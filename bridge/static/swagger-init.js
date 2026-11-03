window.addEventListener("load", function () {
  window.ui = SwaggerUIBundle({
    url: "/openapi.json",
    dom_id: "#swagger-ui",
    presets: [SwaggerUIBundle.presets.apis],
    layout: "BaseLayout",
    deepLinking: true,
    tryItOutEnabled: true,
    displayRequestDuration: true,
    defaultModelsExpandDepth: -1,
    persistAuthorization: false,
    validatorUrl: null,
    queryConfigEnabled: false,
    supportedSubmitMethods: ["get", "post"]
  });
});
