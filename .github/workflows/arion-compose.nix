{ pkgs, frontendBuildWithCaddy }:
{
  project.name = "streetfight";
  services = {

    webserver = {
      image.enableRecommendedContents = true;
      service.useHostStore = true;
      # service.command = [ "sh" "-c" ''
      #             cd "$$CADDY_ROOT"
      #             ${pkgs.python3}/bin/python -m http.server
      #           '' ];
      service.ports = [
        "80:80"
        "443:443"
      ];
      service.environment.CADDY_ROOT = frontendBuildWithCaddy;
      service.stop_signal = "SIGINT";
    };
  };
}
