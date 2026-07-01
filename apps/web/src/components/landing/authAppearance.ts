// Clerk appearance theme for the Stencil auth pages. Colors/fonts/radius are
// driven through Clerk's supported `variables`; structural blending into the
// branding panel is done with scoped .cl-* overrides in auth.css.
// This only restyles Clerk — it does not change any auth behavior.

export const stencilAuthAppearance = {
  variables: {
    colorPrimary: "#ff4d1f",
    colorText: "#f5f1e8",
    colorTextSecondary: "#b9b0a1",
    colorTextOnPrimaryBackground: "#ffffff",
    colorBackground: "#0a0908",
    colorInputBackground: "#0a0908",
    colorInputText: "#f5f1e8",
    colorNeutral: "#f5f1e8",
    colorDanger: "#ff4d1f",
    borderRadius: "2px",
    fontFamily: "var(--font-stencil-body), Georgia, serif",
    fontFamilyButtons: "var(--font-stencil-mono), ui-monospace, monospace",
  },
};
