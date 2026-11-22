import Link from "next/link";
import { Suspense } from "react";
import { getEvents } from "@/lib/api";

async function EventFeed() {
  const events = await getEvents();

  if (events.length === 0) {
    return (
      <p className="text-gray-500">
        Todavía no hay acontecimientos aprobados.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
      {events.map((event) => (
        <Link
          key={event.id}
          href={`/events/${event.id}`}
          className="group relative block aspect-[4/5] overflow-hidden rounded-xl bg-gray-800 shadow-md"
        >
          {event.image_url && (
            <img
              src={event.image_url}
              alt=""
              className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
            />
          )}

          <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/40 to-transparent" />

          <div className="absolute inset-x-0 bottom-0 p-5 text-white">
            <div className="mb-3 flex flex-wrap gap-2">
              <span className="rounded bg-white px-2 py-1 text-xs font-semibold text-black">
                {event.article_count} artículos
              </span>

              <span className="rounded bg-white px-2 py-1 text-xs font-semibold text-black">
                {event.source_count} fuentes
              </span>
            </div>

            <h2 className="text-xl font-bold leading-snug">
              {event.title}
            </h2>
          </div>
        </Link>
      ))}
    </div>
  );
}

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link href="/" className="text-2xl font-bold">
            Paraguay News
          </Link>

          <nav className="flex gap-6 text-sm">
            <Link href="/">Inicio</Link>
            <Link href="/datos">Datos</Link>
          </nav>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-6 py-10">
        <h1 className="mb-2 text-3xl font-bold">
          Últimas noticias
        </h1>

        <p className="mb-8 text-gray-500">
          Los acontecimientos de Paraguay desde múltiples fuentes.
        </p>

        <Suspense
          fallback={
            <p className="text-gray-500">
              Cargando noticias...
            </p>
          }
        >
          <EventFeed />
        </Suspense>
      </section>
    </main>
  );
}