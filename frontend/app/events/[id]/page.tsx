
import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { getEvent } from "@/lib/api";

async function EventDetails({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const eventId = Number(id);

  if (!Number.isSafeInteger(eventId) || eventId <= 0) {
    notFound();
  }

  let event;

  try {
    event = await getEvent(eventId);
  } catch (error) {
    if (
      error instanceof Error &&
      error.message.includes("404")
    ) {
      notFound();
    }

    throw error;
  }

  const articles = [...event.articles].sort((a, b) => {
    const dateA = a.published_at
      ? new Date(a.published_at).getTime()
      : 0;
    const dateB = b.published_at
      ? new Date(b.published_at).getTime()
      : 0;

    return dateB - dateA;
  });

  return (
    <article className="mx-auto max-w-4xl px-6 py-10">
      <Link
        href="/"
        className="text-sm font-medium text-blue-700 hover:underline"
      >
        ← Volver al inicio
      </Link>

      <h1 className="mt-6 text-4xl font-bold leading-tight text-slate-900">
        {event.title}
      </h1>

      <div className="mt-4 flex gap-4 text-sm text-slate-500">
        <span>{event.article_count} artículos</span>
        <span>{event.source_count} fuentes</span>
      </div>

      {event.image_url && (
        <img
          src={event.image_url}
          alt={event.title}
          className="mt-8 aspect-video w-full rounded-xl object-cover"
        />
      )}

      <section className="mt-10">
        <h2 className="mb-4 text-2xl font-bold">
          Resumen del acontecimiento
        </h2>

        <div className="whitespace-pre-line text-lg leading-8 text-slate-700">
          {event.summary}
        </div>
      </section>

      <section className="mt-12 border-t border-slate-200 pt-8">
        <h2 className="text-2xl font-bold">
          Cobertura de los medios
        </h2>

        <p className="mt-2 text-sm text-slate-500">
          {event.article_count} artículos de {event.source_count} fuentes
        </p>

        <div className="mt-6 divide-y divide-slate-200">
          {articles.map((article) => {
            const domain = article.source_domain
              .replace(/^https?:\/\//, "")
              .replace(/^www\./, "")
              .split("/")[0];

            return (
              <div
                key={article.id}
                className="flex items-start gap-4 py-5"
              >
                <img
                  src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`}
                  alt=""
                  className="mt-1 h-9 w-9 rounded object-contain"
                />

                <div>
                  <p className="mb-1 text-sm text-slate-500">
                    {article.source_name}
                    {article.published_at &&
                      ` · ${new Date(
                        article.published_at
                      ).toLocaleString("es-PY", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        timeZone: "America/Asuncion",
                      })}`}
                  </p>

                  <a
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-lg font-semibold text-slate-900 hover:text-blue-700 hover:underline"
                  >
                    {article.title} ↗
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </article>
  );
}

export default function EventPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return (
    <main className="min-h-screen bg-white">
      <Suspense
        fallback={
          <div className="mx-auto max-w-4xl px-6 py-10 text-slate-500">
            Cargando acontecimiento...
          </div>
        }
      >
        <EventDetails params={params} />
      </Suspense>
    </main>
  );
}

