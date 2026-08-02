import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import SiteApp from "./SiteApp";
import "./styles.css";
import "./site-styles.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("CoupFE–EDA workbench root element is missing.");
}

createRoot(root).render(
  <StrictMode>
    <SiteApp />
  </StrictMode>,
);
