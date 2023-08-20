import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from "react-router-dom";


import AdminMode from './AdminMode';

export default function App() {
  return (


    <BrowserRouter>
      <Routes>
        <Route path="*" element={<AdminMode />} />
      </Routes>
    </BrowserRouter>

  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
