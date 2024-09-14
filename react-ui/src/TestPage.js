
import React, {  useEffect } from "react";

// import addToHomescreen from 'add-to-homescreen';
// import 'add-to-homescreen/dist/style/addtohomescreen.css';

const addToHomescreen = require('add-to-homescreen/src/addtohomescreen');

const AddToHomeScreen = () => {
  useEffect(() => {


    console.log(addToHomescreen);


    // // Initialize the add-to-homescreen prompt
    // addToHomescreen({
    //   startDelay: 0, // Start immediately after page load
    //   lifespan: 15,  // How long to display the prompt (in seconds)
    //   autostart: true, // Automatically show the prompt
    //   maxDisplayCount: 2, // Show a maximum of two times
    // });
  }, []);



  return (
    <div>
      <h1>My React App</h1>
    </div>
  );
};

export default AddToHomeScreen;
