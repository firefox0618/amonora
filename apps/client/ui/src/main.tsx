import React from "react";
import ReactDOM from "react-dom/client";
import { MantineProvider, createTheme } from "@mantine/core";
import App from "./App";
import "@mantine/core/styles.css";
import "./styles.css";

declare global {
  interface Window {
    __AMONORA_CLIENT_TOKEN__?: string;
    __AMONORA_CLIENT_API_BASE__?: string;
  }
}

const theme = createTheme({
  primaryColor: "grape",
  defaultRadius: "lg",
  fontFamily: "\"Segoe UI Variable Text\", \"Segoe UI\", system-ui, sans-serif",
  headings: {
    fontFamily: "\"Segoe UI Variable Display\", \"Segoe UI\", system-ui, sans-serif",
  },
  colors: {
    grape: [
      "#fff0f8",
      "#f9dff0",
      "#f1bfdc",
      "#e89dc7",
      "#de7ab1",
      "#cd5d95",
      "#ae4778",
      "#88355d",
      "#612442",
      "#3d142a"
    ],
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark">
      <App />
    </MantineProvider>
  </React.StrictMode>,
);
