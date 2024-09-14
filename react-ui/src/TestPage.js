
import React, { useEffect, useState } from "react";


// require('add-to-homescreen/dist/add-to-homescreen.min.js');
// require('add-to-homescreen/dist/add-to-homescreen.min.css');

require('add-to-homescreen/src/addtohomescreen');
const css = require("add-to-homescreen/style/all.min.css");



const TestPage = () => {
  const [text, setText] = useState("Not set yet");

  useEffect(() => {
    // setText("starting...");

    var ath = window.addToHomescreen({
      autostart: true,
      startDelay: 2,
      onShow: function () {
        setText("showing");
      },
      onInit: function () {
        setText("initializing");
      },
      onAdd: function () {
        setText("adding");
      },
      onInstall: function () {
        setText("Installing");
      },
      onCancel: function () {
        setText("Cancelling");
      }
    });

    console.log("window.addToHomescreen:", window.addToHomescreen);

    console.log("CSS:", css);

    // setText("completed!");
  }, []);

  return (
    <div>
      <h1>This is a test</h1>

      {text}
    </div>
  );
};

export default TestPage;
