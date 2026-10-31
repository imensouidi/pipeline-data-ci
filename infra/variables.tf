variable "subscription_id" {
  description = "ID de l'abonnement Azure for Students"
  type        = string
}

variable "location" {
  description = "Région Azure"
  type        = string
  default     = "francecentral"
}

variable "resource_group_name" {
  description = "Nom du groupe de ressources"
  type        = string
  default     = "rg-pipeline-data"
}

variable "container_group_name" {
  description = "Nom du groupe de conteneurs (SeaweedFS + pipeline)"
  type        = string
  default     = "ci-pipeline-data"
}

variable "pipeline_image" {
  description = "Image Docker de la pipeline (poussée sur Docker Hub, ex : docker.io/moncompte/pipeline-data:latest)"
  type        = string
}

variable "s3_access_key" {
  description = "Clé d'accès S3 (utilisée par boto3 ; SeaweedFS est lancé sans authentification)"
  type        = string
  sensitive   = true
}

variable "s3_secret_key" {
  description = "Clé secrète S3"
  type        = string
  sensitive   = true
}
