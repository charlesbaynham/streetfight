
import React, { useEffect, useState } from "react";


require('add-to-homescreen/dist/add-to-homescreen.min.js');
require('add-to-homescreen/dist/add-to-homescreen.min.css');


const TestPage = () => {
  const [text, setText] = useState("Not set yet");

  useEffect(() => {
    setText("DOMContentLoaded starting");

    window.AddToHomeScreenInstance = new window.AddToHomeScreen({
      appName: 'Streetfight',
      appIconUrl: 'logo512.png',
      assetUrl: 'https://cdn.jsdelivr.net/gh/philfung/add-to-homescreen@2.0/dist/assets/img/',
      maxModalDisplayCount: -1
    });

    window.AddToHomeScreenInstance.show('en');

    setText("DOMContentLoaded completed");
  }, []);

  return (
    <div>
      <h1>This is a test</h1>

      {text}
    </div>
  );
};

export default TestPage;
