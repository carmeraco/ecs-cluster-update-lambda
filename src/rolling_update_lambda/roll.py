""" Drain running ECS services from an instance about to be terminated."""
import json
import logging
import time
import boto3
import math
import os

DEFAULT_MAX_ITERATIONS_PER_INSTANCE = 10
# Stagger execution to avoid spamming SNS
DEFAULT_PAUSE = 30  # seconds

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

session = boto3.session.Session()
resource_client = session.client(service_name='resourcegroupstaggingapi')
asg_client = session.client(service_name='autoscaling')
ec2_client = session.client(service_name='ec2')
sns_client = session.client(service_name='sns')
lambda_client = session.client(service_name='lambda')


def describe_asg(asg_name):
    """ Describe ASG.  Return just 1 asg

    Args:
        asg_arn (str): ASG ARN

    Returns:
        list: Instance IDs of EC2 instances
    """
    logger.info('Trying to describe ASG %s...', asg_name)
    group_response = asg_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[asg_name]
    )
    if len(group_response['AutoScalingGroups']) != 1:
        logger.error('Unable to describe ASG: %s...', asg_name)
        logger.error(
            'Found %s groups',
            str(len(group_response['AutoScalingGroups']))
        )
        raise
    return group_response['AutoScalingGroups'][0]


def get_asg_instance_health(asg_data):
    """ Parse Instance IDs and Health Status from Describe ASG data

    Args:
        asg_data (list): Describe ASG output for 1 ASG object

    Returns:
        list: Dicts of Instance IDs and ASG Health Status of EC2 instances
    """
    raw_instances = asg_data['Instances']
    return [
        {'id': i['InstanceId'], 'health': i['HealthStatus']}
        for i in raw_instances
    ]


def get_ec2_instances(asg_data):
    """ Parse Instance IDs from Describe ASG data

    Args:
        asg_data (list): Describe ASG output for 1 ASG object

    Returns:
        list: Instance IDs contained EC2 instances
    """
    raw_instances = asg_data['Instances']
    return [i['InstanceId'] for i in raw_instances]


def publish_to_sns(message, subject, topic_arn):
    """ Publish message to SNS topic to invoke lambda again.

    Args:
        message (JSON): updated message to send
        subject (str): subject of the message
        topic_arn (str): ARN of SNS topic
    """

    logger.info('Sending message to SNS...')
    sns_client.publish(
        TopicArn=topic_arn,
        Message=json.dumps(message),
        Subject=subject
    )


def set_drain_tag(instance_ids, drain):
    """ Set "drain" tag for all instances in the list.

    Args:
        instance_ids (list): EC2 instance ids that need to be tagged
        drain (bool): True if instances are tainted, False otherwise
    """

    logger.info('Setting "drain" tag to %s', drain)
    logger.info('Instance ids %s', instance_ids)

    ec2_client.create_tags(
        DryRun=False,
        Resources=instance_ids,
        Tags=[
            {
                'Key': 'drain',
                'Value': str(drain).lower()
            }
        ]
    )


def handler(event, context):
    """ Main lambda handler.

    Process incoming SNS message.
    - If this is the start of lifecycle hook, find autoscaling group and
      list instance ids
    - Call the tag_lambda function
    - Increase the ASG size and set original in meta
    - Check the number of healthy hosts in ASG:
        - ASG terminate (healthy count - original size) instances
        - If any original instances exist, sleep and put a new SNS message in
    """
    logger.info('Starting execution')
    message = json.loads(event['Records'][0]['Sns']['Message'])

    # Check that asg has been specified
    if 'asg_name' not in message.keys():
        logger.info("No asg specified, skipping.")
        return 1

    # Set default pause between iterations
    if 'pause' not in message.keys():
        message['pause'] = DEFAULT_PAUSE

    dry = 'dry_run' in message and message['dry_run']

    # Get ASG and instance state
    asg_data = describe_asg(message['asg_name'])
    current_inst_status = get_asg_instance_health(asg_data)

    # Setup rolling update process if it hasn't been done already
    if 'ec2_inst_ids' not in message.keys():
        # Set metadata
        message['ec2_inst_ids'] = get_ec2_instances(asg_data)
        message['asg_max'] = asg_data['MaxSize']
        message['asg_desired'] = asg_data['DesiredCapacity']
        message['asg_count'] = len(current_inst_status)
        message['iter'] = 1
        if 'iters_per_inst' in message.keys():
            iter_multiple = 'iters_per_inst' in message.keys()
        else:
            iter_multiple = DEFAULT_MAX_ITERATIONS_PER_INSTANCE
        message['max_iters'] = iter_multiple * len(message['ec2_inst_ids'])
        if 'growth_percent' not in message.keys():
            message['growth_percent'] = 20

        logger.info('Rolling update metadata: %s', str(message))

        if dry:
            logger.info('DRY RUN: Tag instances to prevent scheduling:\n %s',
                        message['ec2_inst_ids'])
        else:
            set_drain_tag(message['ec2_inst_ids'], True)

        # Increase number of instances to accept load
        growth_mult = message['growth_percent'] / 100
        additional_instances = math.ceil(message['asg_desired'] * growth_mult)
        target_count = message['asg_desired'] + additional_instances

        asgargs = {
            'AutoScalingGroupName': message['asg_name'],
            'DesiredCapacity': target_count
        }
        if target_count > message['asg_max']:
            asgargs['MaxSize'] = target_count

        if dry:
            logger.info(
                'DRY_RUN: Update ASG "%s" with values:\n %s',
                message['asg_name'],
                str(asgargs)
            )
        else:
            asg_client.update_auto_scaling_group(**asgargs)

        # Sleep the pause time to wait for instances to be created
        if dry:
            logger.info(
                'DRY_RUN: Sleep for %s to wait for instance creation',
                message['pause']
            )
        else:
            time.sleep(message['pause'])

        # Get new cluster data
        asg_data = describe_asg(message['asg_name'])
        current_inst_status = get_asg_instance_health(asg_data)

    # Check group health against terminating instances as appropriate
    healthy_instances = list(filter(
        lambda h: h['health'] == 'Healthy', current_inst_status
    ))
    healthy_instance_count = len(healthy_instances)
    instance_difference = healthy_instance_count - message['asg_count']
    if dry:
        instance_difference = 1
    while instance_difference > 0:
        input = {
            'InstanceId': message['ec2_inst_ids'].pop(),
            'ShouldDecrementDesiredCapacity': False
        }
        if dry:
            logger.info(
                'DRY_RUN: Terminate instance:\n %s',
                str(input)
            )
        else:
            asg_client.terminate_instance_in_auto_scaling_group(**input)
        instance_difference -= 1

    topic_arn = event['Records'][0]['Sns']['TopicArn']

    if len(message['ec2_inst_ids']) < 1:
        logger.info('No EC2 Instances left.  Rolling update completed.')
        return
    else:
        message['iter'] += 1

        # Circuit breaker
        if message['iter'] > message['max_iters']:
            logger.error(
                'Exceeded the maximum number of iterations, ending loop.')
            return
        logger.info('Pausing to wait for scaling operations to complete.')
        if dry:
            logger.info(
                'DRY RUN: %s instances remaining. Would sleep for %s',
                str(len(message['ec2_inst_ids'])),
                message['pause']
            )
        else:
            time.sleep(message['pause'])
        subject = 'Rolling update of asg: {}'.format(message['asg_name'])
        if dry:
            logger.info(
                'DRY RUN: Publishing to SNS Topic %s:\n Subject: %s,\n %s',
                topic_arn,
                subject,
                str(message)
            )
        else:
            publish_to_sns(message, subject, topic_arn)
        return


# Below to use if calling locally for testing purposes
if __name__ == '__main__':
    event = {
        'Records': [
            {
                'Sns': {
                    'Message': json.dumps({
                        'dry_run': True,
                        'growth_percent': 400,
                        'asg_name': 'dev-ecs-cluster'
                    }),
                    'TopicArn': 'dev-ecs-roll'
                }
            }
        ]
    }
    handler(event, {})
