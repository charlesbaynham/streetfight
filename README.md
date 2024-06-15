# Streetfight

This app is not ready for people other than me to use. If you are reading this readme, you're probably not me. So good luck!

Dev mode:

1. `npm i`
2. `npm run backend` in one terminal, `npm run dev` in other

Production:

1. Configure `.env`

either:

2. Run `nix run .#frontend` in one window
3. ...and `nix run .#backend` in another

or:

2. `nix run` to build docker images and store them in the local registry
3. `docker compose up`
