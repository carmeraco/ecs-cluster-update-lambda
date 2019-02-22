output "sns_arn" {
  value = "${aws_sns_topic.asg_updates.arn}"
}

output "roll_sns_arn" {
  value = "${aws_sns_topic.asg_rolling_updates.arn}"
}
