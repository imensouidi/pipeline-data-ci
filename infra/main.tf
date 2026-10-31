# Groupe de ressources : conteneur logique qui regroupe toutes les ressources du projet.
resource "azurerm_resource_group" "pipeline" {
  name     = var.resource_group_name
  location = var.location
}

# Groupe de conteneurs (Azure Container Instances) :
# - SeaweedFS (service S3) et la pipeline partagent le même réseau, donc la pipeline
#   joint SeaweedFS sur http://localhost:8333.
# - ip_address_type = "None" : aucun port exposé sur Internet.
resource "azurerm_container_group" "pipeline" {
  name                = var.container_group_name
  location            = azurerm_resource_group.pipeline.location
  resource_group_name = azurerm_resource_group.pipeline.name
  os_type             = "Linux"
  ip_address_type     = "None"
  restart_policy      = "Always"

  container {
    name   = "seaweedfs"
    image  = "chrislusf/seaweedfs:latest"
    cpu    = "1"
    memory = "1.5"

    commands = ["weed", "server", "-s3", "-s3.port=8333", "-dir=/data"]
  }

  container {
    name   = "pipeline"
    image  = var.pipeline_image
    cpu    = "0.5"
    memory = "1"

    commands = ["python", "-m", "pipeline", "--n-files", "5", "--seed", "42", "--every", "300"]

    environment_variables = {
      S3_ENDPOINT = "http://localhost:8333"
    }

    secure_environment_variables = {
      S3_ACCESS_KEY = var.s3_access_key
      S3_SECRET_KEY = var.s3_secret_key
    }
  }
}
