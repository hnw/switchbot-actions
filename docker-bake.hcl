# docker-bake.hcl

group "default" {
  targets = ["app", "app-armv6"]
}

target "app" {
  context    = "."
  dockerfile = "Dockerfile"
  platforms  = ["linux/amd64", "linux/arm64", "linux/arm/v7"]
}

target "app-armv6" {
  context    = "."
  dockerfile = "Dockerfile.armv6"
  platforms  = ["linux/arm/v6"]
}
