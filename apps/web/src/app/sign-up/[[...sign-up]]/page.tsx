import { SignUp } from "@clerk/nextjs";
import { stencilAuthAppearance } from "@/components/landing/authAppearance";
import { stencilFontVars } from "@/components/landing/fonts";
import { StencilAuth } from "@/components/landing/StencilAuth";

export default function SignUpPage() {
  return (
    <StencilAuth mode="signup" className={stencilFontVars}>
      <SignUp appearance={stencilAuthAppearance} signInUrl="/sign-in" />
    </StencilAuth>
  );
}
