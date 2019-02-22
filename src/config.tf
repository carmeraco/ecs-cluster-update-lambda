variable "region" {}

variable "drain_lambda_name" {
  default = "drain-ecs-lambda"
}

variable "rebalance_lambda_name" {
  default = "rebalance-ecs-lambda"
}

variable "roll_lambda_name" {
  default = "roll-ecs-lambda"
}

variable "roll_topic_name" {
  default = "ecs-cluster-rolling-update"
}

variable "sns_topic_name" {
  default = "ecs-cluster-updates"
}

variable "tags" {
  type = "map"

  default = {
    created-by = "terraform"
  }
}
