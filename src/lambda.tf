##############################################################
# drain-ecs-lambda
##############################################################
data "archive_file" "drain_lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/drain_lambda"
  output_path = "${path.module}/drain_lambda.zip"
}

resource "aws_lambda_function" "drain_lambda" {
  filename         = "${data.archive_file.drain_lambda_zip.output_path}"
  source_code_hash = "${data.archive_file.drain_lambda_zip.output_base64sha256}"
  role             = "${aws_iam_role.drain_lambda.arn}"
  function_name    = "${var.drain_lambda_name}"
  description      = "Gracefully migrate ECS tasks from container instance about to be terminated"
  handler          = "drain.handler"
  runtime          = "python3.6"
  timeout          = 300
  tags             = "${merge(var.tags, map("function-name", "drain-instances"))}"
}

##############################################################
# rolling-update-ecs-lambda
##############################################################
data "archive_file" "roll_lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/rolling_update_lambda"
  output_path = "${path.module}/roll_lambda.zip"
}

resource "aws_lambda_function" "roll_lambda" {
  filename         = "${data.archive_file.roll_lambda_zip.output_path}"
  source_code_hash = "${data.archive_file.roll_lambda_zip.output_base64sha256}"
  role             = "${aws_iam_role.roll_lambda.arn}"
  function_name    = "${var.roll_lambda_name}"
  description      = "Perform a rolling update of an AutoScaling group"
  handler          = "roll.handler"
  runtime          = "python3.6"
  timeout          = 300

  environment {
    variables = {
      REBALANCE_LAMBDA_NAME = "${aws_lambda_function.rebalance_lambda.function_name}"
    }
  }

  tags = "${merge(var.tags, map("function-name", "rolling-update"))}"
}

##############################################################
# rebalance-ecs-lambda
##############################################################
data "archive_file" "rebalance_lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/rebalance_lambda"
  output_path = "${path.module}/rebalance_lambda.zip"
}

resource "aws_lambda_function" "rebalance_lambda" {
  filename         = "${data.archive_file.rebalance_lambda_zip.output_path}"
  source_code_hash = "${data.archive_file.rebalance_lambda_zip.output_base64sha256}"
  role             = "${aws_iam_role.rebalance_lambda.arn}"
  function_name    = "${var.rebalance_lambda_name}"
  description      = "Rebalance tasks across an ECS cluster"
  handler          = "rebalance.lambda_handler"
  runtime          = "python3.6"
  timeout          = 300

  tags = "${merge(var.tags, map("function-name", "rebalance"))}"
}
