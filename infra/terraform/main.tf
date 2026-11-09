# Describes the local CDC stack. `terraform validate` checks this file.
# It does not create cloud resources and it does not spend anything.

terraform {
  required_version = ">= 1.5.0"
}

variable "postgres_image" {
  type    = string
  default = "postgres:16"
}

variable "redpanda_image" {
  type    = string
  default = "docker.redpanda.com/redpandadata/redpanda:v24.2.18"
}

variable "debezium_image" {
  type    = string
  default = "quay.io/debezium/server:2.7.3.Final"
}

variable "kafka_topic_prefix" {
  type    = string
  default = "agedcare"
}

output "cdc_stack" {
  value = {
    postgres = var.postgres_image
    redpanda = var.redpanda_image
    debezium = var.debezium_image
    topic    = "${var.kafka_topic_prefix}.registry.services"
  }
}

check "images_are_pinned" {
  assert {
    condition     = length(var.postgres_image) > 0 && length(var.debezium_image) > 0
    error_message = "CDC images must be set."
  }
}
