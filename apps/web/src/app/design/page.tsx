import type { Metadata } from "next";
import { ArrowRight, Clock } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CoverImage } from "@/components/ui/CoverImage";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tag } from "@/components/ui/Tag";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { Container } from "@/components/layout/Container";
import { Prose } from "@/components/layout/Prose";

export const metadata: Metadata = {
  title: "Design system",
  robots: { index: false, follow: false },
};

const SWATCHES = [
  ["page", "bg-page"],
  ["surface", "bg-surface"],
  ["sunken", "bg-sunken"],
  ["line", "bg-line"],
  ["ink", "bg-ink"],
  ["muted", "bg-muted"],
  ["accent", "bg-accent"],
  ["on-accent", "bg-on-accent"],
] as const;

const TYPE = [
  ["Display", "text-display font-semibold", "Display 56"],
  ["H1", "text-h1 font-semibold", "Heading 56"],
  ["H2", "text-h2 font-semibold", "Heading 40"],
  ["H3", "text-h3 font-semibold", "Heading 28"],
  ["Lead", "text-lead", "Lead 20"],
  ["Body", "text-body", "Body 17, line height 28"],
  ["Small", "text-small text-muted", "Small 15"],
  ["Caption", "text-caption text-muted", "Caption 13"],
] as const;

const COVERS = [
  ["pattern-one", "a"],
  ["pattern-two", "b"],
  ["pattern-three", "c"],
  ["pattern-four", "d"],
] as const;

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-6 border-t border-line py-12">
      <h2 className="text-small font-semibold uppercase tracking-wider text-muted">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function DesignPage() {
  return (
    <main>
      <Container className="pb-16">
        <div className="flex items-center justify-between py-6">
          <span className="text-lead font-semibold">Design system</span>
          <ThemeToggle />
        </div>
        <p className="rounded-control bg-sunken px-4 py-3 text-caption text-muted">
          Reference page for the tokens and components. Use the toggle to check
          light, dark and system themes.
        </p>

        <Section title="Colour tokens">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {SWATCHES.map(([name, cls]) => (
              <div
                key={name}
                className="rounded-control border border-line p-3 text-caption"
              >
                <div
                  className={`mb-2 h-10 rounded-control border border-line ${cls}`}
                />
                {name}
              </div>
            ))}
          </div>
        </Section>

        <Section title="Type scale">
          <div className="flex flex-col gap-2">
            {TYPE.map(([name, cls, sample]) => (
              <p key={name} className={cls} title={name}>
                {sample}
              </p>
            ))}
            <p className="font-serif text-h3 font-semibold">
              Serif heading, Source Serif
            </p>
            <p className="font-serif text-body">
              Serif body text for articles, set in Source Serif.
            </p>
          </div>
        </Section>

        <Section title="Buttons">
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <Button>
                Read article{" "}
                <ArrowRight aria-hidden="true" className="size-4" />
              </Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="ghost">Ghost</Button>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button size="sm">Small</Button>
              <Button size="sm" variant="secondary">
                Small
              </Button>
              <Button size="sm" variant="ghost">
                Small
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button disabled>Disabled</Button>
              <Button variant="secondary" disabled>
                Disabled
              </Button>
              <Button variant="ghost" disabled>
                Disabled
              </Button>
            </div>
            <p className="text-caption text-muted">
              Hover: ghost gains the sunken background; primary and secondary
              keep their fill. Keyboard focus shows a two pixel ring.
            </p>
          </div>
        </Section>

        <Section title="Tags">
          <div className="flex flex-wrap gap-2">
            <Tag>Models</Tag>
            <Tag>Research</Tag>
            <Tag href="#tags">Link tag</Tag>
          </div>
        </Section>

        <Section title="Cards">
          <div className="grid gap-6 sm:grid-cols-2">
            <Card className="flex flex-col gap-3 p-6">
              <p className="text-caption text-muted">Plain card</p>
              <h3 className="font-serif text-h3 font-semibold">
                Sparse attention cuts long-context cost
              </h3>
              <p className="text-small text-muted">
                Static surface with a hairline border and no shadow.
              </p>
            </Card>
            <Card interactive className="flex flex-col gap-3 p-6">
              <p className="flex items-center gap-1 text-caption text-muted">
                <Clock aria-hidden="true" className="size-4" /> Interactive card
              </p>
              <h3 className="font-serif text-h3 font-semibold">
                Hover for the soft shadow
              </h3>
              <p className="text-small text-muted">
                Adds one soft shadow on hover.
              </p>
            </Card>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {COVERS.map(([slug, label]) => (
              <Card key={slug} interactive className="overflow-hidden">
                <CoverImage slug={slug} alt={`Fallback cover ${label}`} />
                <div className="p-4 text-caption text-muted">
                  Cover fallback {label}
                </div>
              </Card>
            ))}
          </div>
        </Section>

        <Section title="Inputs">
          <div className="grid max-w-md gap-6">
            <Input label="Search articles" placeholder="Try long context" />
            <Input
              label="Email"
              defaultValue="not an email"
              error="Enter a valid email address."
            />
          </div>
        </Section>

        <Section title="Skeleton">
          <div className="flex max-w-md flex-col gap-3">
            <Skeleton className="h-4 w-4/5" />
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        </Section>

        <Section title="Theme toggle">
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <span className="text-small text-muted">
              Cycles light, dark, system.
            </span>
          </div>
        </Section>

        <Section title="Prose">
          <Prose>
            <h2>What the results show</h2>
            <p>
              Long inputs are expensive because attention cost grows with the
              square of the sequence. See the <a href="#prose">paper notes</a>{" "}
              and the inline <code>window=4096</code> setting.
            </p>
            <ul>
              <li>About 33% lower compute at 128k tokens.</li>
              <li>No gain below 8k tokens.</li>
            </ul>
            <blockquote>
              The saving depends on keeping the dense layers.
            </blockquote>
          </Prose>
        </Section>
      </Container>
    </main>
  );
}
