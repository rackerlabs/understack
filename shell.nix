let
  nixpkgs = fetchTarball {
  name = "nixos-unstable-2024-02-20";
  url = "https://github.com/NixOS/nixpkgs/archive/8a8350636615bb49841af183cf9399289e570738.tar.gz";
  };
  pkgs = import nixpkgs { config = {}; overlays = []; };
in

pkgs.mkShellNoCC {
  packages = with pkgs; [
    kubectl
    kubernetes-helm
    kubeseal
    kustomize
    yq
  ];
}
