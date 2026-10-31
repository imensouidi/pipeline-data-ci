output "resource_group" {
  description = "Groupe de ressources créé"
  value       = azurerm_resource_group.pipeline.name
}

output "container_group" {
  description = "Groupe de conteneurs (SeaweedFS + pipeline)"
  value       = azurerm_container_group.pipeline.name
}
