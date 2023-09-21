FROM nixpkgs/nix-flakes

USER root

# Install git
RUN . /home/root/.nix-profile/etc/profile.d/nix.sh \
  && nix-env -i git git-lfs

# Copy app files
RUN mkdir /app
COPY backend /app/
