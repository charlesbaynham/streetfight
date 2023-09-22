FROM nixpkgs/nix-flakes

USER root

# Install git
RUN nix profile install nixpkgs#git nixpkgs#git-lfs

# Copy app files
RUN mkdir /app
COPY backend /app/

# Build app
