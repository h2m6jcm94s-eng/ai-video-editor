import { SignIn } from "@clerk/nextjs";
import { stencilAuthAppearance } from "@/components/landing/authAppearance";
import { stencilFontVars } from "@/components/landing/fonts";
import { StencilAuth } from "@/components/landing/StencilAuth";

export default function SignInPage() {
  return (
    <StencilAuth mode="signin" className={stencilFontVars}>
      <SignIn appearance={stencilAuthAppearance} />
    </StencilAuth>
  );
}
