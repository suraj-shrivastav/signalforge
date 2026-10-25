import { safeHref } from "@/lib/format";
import type { PublicTable } from "@/lib/public";

// A source table, copied by the pipeline. Scrolls sideways on a narrow screen instead of
// breaking the layout; the source is named under it.
export function ArticleTable({ table }: { table: PublicTable }) {
  const href = table.source ? safeHref(table.source.url) : null;
  return (
    <figure className="mt-10">
      <div className="overflow-x-auto rounded-tile bg-surface">
        <table className="w-full min-w-max border-collapse text-left text-small">
          {table.caption && (
            <caption className="px-5 pt-4 text-left text-caption font-semibold text-muted">
              {table.caption}
            </caption>
          )}
          <thead className="bg-sunken">
            <tr>
              {table.header.map((cell, i) => (
                <th
                  key={i}
                  scope="col"
                  className="px-5 py-3 font-semibold text-ink"
                >
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, r) => (
              <tr key={r} className="border-t border-line">
                {row.map((cell, i) =>
                  i === 0 ? (
                    <th
                      key={i}
                      scope="row"
                      className="px-5 py-3 text-left font-semibold text-ink"
                    >
                      {cell}
                    </th>
                  ) : (
                    <td key={i} className="px-5 py-3 tabular-nums text-ink">
                      {cell}
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.source && (
        <figcaption className="mt-2 text-caption text-muted">
          Source:{" "}
          {href ? (
            <a
              href={href}
              rel="noopener noreferrer"
              className="underline underline-offset-2"
            >
              {table.source.label}
            </a>
          ) : (
            table.source.label
          )}
        </figcaption>
      )}
    </figure>
  );
}
