# Alarms on the three things that kill this box quietly.
#
# The topic is created here; the email subscription is NOT. Subscribing by
# email would put a personal address into a configuration file in a PUBLIC
# repository, which is spam bait and exactly the kind of thing CLAUDE.md's
# privacy rule exists to prevent. It is also a poor fit for Terraform: an email
# subscription sits in "pending confirmation" until someone clicks a link, which
# shows up as perpetual drift. Subscribe by hand instead (see the handoff).

resource "aws_sns_topic" "alerts" {
  name         = "carpool-alerts"
  display_name = "carpool"

  tags = {
    Name = "carpool-alerts"
  }
}

# A system status check failure means the underlying host is broken, and the
# fix is to move the instance to different hardware. AWS will do that itself
# via the recover action, which is free and faster than a human noticing.
resource "aws_cloudwatch_metric_alarm" "system_status" {
  alarm_name          = "carpool-system-status-failed"
  alarm_description   = "Underlying host is unhealthy. Auto-recovers to new hardware."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"

  # Absent data here means the instance is not reporting, which is not the same
  # as being unhealthy - a stopped instance would otherwise alarm forever.
  treat_missing_data = "missing"

  dimensions = {
    InstanceId = aws_instance.app.id
  }

  alarm_actions = [
    "arn:aws:automate:${var.region}:ec2:recover",
    aws_sns_topic.alerts.arn,
  ]
  ok_actions = [aws_sns_topic.alerts.arn]
}

# An instance status check failure is the guest's problem - a full disk, a
# kernel panic, a broken network config. Recovery would not help, because the
# same broken disk comes back with it. This one only tells a human.
resource "aws_cloudwatch_metric_alarm" "instance_status" {
  alarm_name          = "carpool-instance-status-failed"
  alarm_description   = "Guest OS is unhealthy. Needs a look, not a recover."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_Instance"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "missing"

  dimensions = {
    InstanceId = aws_instance.app.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# The instance runs in `standard` credit mode (instance.tf), so an exhausted
# balance means throttling to baseline rather than a surprise charge. That is
# the intended trade, but it is worth knowing before the box gets slow: a
# draining balance usually means something is looping, not that traffic grew.
resource "aws_cloudwatch_metric_alarm" "cpu_credits" {
  alarm_name          = "carpool-cpu-credits-low"
  alarm_description   = "CPU credit balance draining. In standard mode this ends in throttling."
  namespace           = "AWS/EC2"
  metric_name         = "CPUCreditBalance"
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.cpu_credit_alarm_threshold
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "missing"

  dimensions = {
    InstanceId = aws_instance.app.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}
