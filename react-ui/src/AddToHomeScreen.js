require("add-to-homescreen/dist/add-to-homescreen.min.js");
require("add-to-homescreen/dist/add-to-homescreen.min.css");

export function prepareInstallPrompt() {
  // Prepare to show install prompt
  window.AddToHomeScreenInstance = new window.AddToHomeScreen({
    appName: "Streetfight",
    appIconUrl: "logo512.png",
    assetUrl:
      "https://cdn.jsdelivr.net/gh/philfung/add-to-homescreen@2.0/dist/assets/img/",
    maxModalDisplayCount: -1,
  });
  console.log("Setup complete");
}

export function isStandalone() {
  return window.AddToHomeScreenInstance.isStandAlone;
}

export function showInstallPrompt() {
  return window.AddToHomeScreenInstance.show("en");
}
