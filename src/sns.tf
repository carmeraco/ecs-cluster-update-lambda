##############################################################
# SNS drain-ecs-lambda
##############################################################
resource "aws_sns_topic" "asg_updates" {
  name         = "${var.sns_topic_name}"
  display_name = "${var.sns_topic_name}"
}

resource "aws_lambda_permission" "allow_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = "${var.drain_lambda_name}"
  principal     = "sns.amazonaws.com"
  source_arn    = "${aws_sns_topic.asg_updates.arn}"

  depends_on = [
    "aws_lambda_function.drain_lambda",
  ]
}

resource "aws_sns_topic_subscription" "lambda" {
  topic_arn = "${aws_sns_topic.asg_updates.arn}"
  protocol  = "lambda"
  endpoint  = "${aws_lambda_function.drain_lambda.arn}"

  depends_on = [
    "aws_lambda_function.drain_lambda",
  ]
}

##############################################################
# SNS roll-ecs-lambda
##############################################################
resource "aws_sns_topic" "asg_rolling_updates" {
  name         = "${var.roll_topic_name}"
  display_name = "${var.roll_topic_name}"
}

resource "aws_lambda_permission" "allow_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = "${var.roll_lambda_name}"
  principal     = "sns.amazonaws.com"
  source_arn    = "${aws_sns_topic.asg_rolling_updates.arn}"

  depends_on = [
    "aws_lambda_function.roll_lambda",
  ]
}

resource "aws_sns_topic_subscription" "roll-lambda" {
  topic_arn = "${aws_sns_topic.asg_rolling_updates.arn}"
  protocol  = "lambda"
  endpoint  = "${aws_lambda_function.roll_lambda.arn}"

  depends_on = [
    "aws_lambda_function.roll_lambda",
  ]
}
