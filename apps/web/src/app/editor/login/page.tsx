import type { Metadata } from "next";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { login } from "./actions";

export const metadata: Metadata = {
  title: "Editor login",
  robots: { index: false, follow: false },
};

const DEFAULT_NEXT = "/editor/signals";

function resolveNext(value: string | undefined): string {
  if (!value || !value.startsWith("/editor/")) return DEFAULT_NEXT;
  return value;
}

export default async function EditorLoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const params = await searchParams;
  const next = resolveNext(params.next);
  const hasError = params.error === "1";

  return (
    <div className="mx-auto flex min-h-screen max-w-sm items-center px-4">
      <Card className="w-full p-8">
        <h1 className="text-h3 text-ink">Editor login</h1>
        <form action={login} className="mt-6 flex flex-col gap-4">
          <input type="hidden" name="next" value={next} />
          <Input
            label="Password"
            type="password"
            name="password"
            required
            autoFocus
          />
          {hasError ? (
            <p role="alert" className="text-caption text-ink">
              Wrong password.
            </p>
          ) : null}
          <Button type="submit">Enter</Button>
        </form>
      </Card>
    </div>
  );
}
