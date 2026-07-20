import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./styles.css";
import { App } from "./AppRoutes";
import { ErrorBoundary } from "./legacy-workspace";

const rootElement = document.getElementById("root");
if (!rootElement) document.body.textContent = "Frontend failed to start.";
else createRoot(rootElement).render(<ErrorBoundary><BrowserRouter><App /></BrowserRouter></ErrorBoundary>);
