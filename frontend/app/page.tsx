
import Link from "next/link";
import { Suspense } from "react";
import { getEvents } from "@/lib/api";
import PartisanBar from "@/components/PartisanBar";
import { Libre_Baskerville } from "next/font/google";

const libreBaskerville = Libre_Baskerville({
  subsets: ["latin"],
  weight: ["400", "700"],
});

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

          {/* Dark gradient over image */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/40 to-transparent" />

          {/* Event information */}
          <div className="absolute inset-x-0 bottom-0 p-5 text-white">

            {/* Article and source counts */}
            <div className="mb-3 flex flex-wrap gap-2">
              <span className="rounded bg-white px-2 py-1 text-xs font-semibold text-black">
                {event.article_count} artículos
              </span>

              <span className="rounded bg-white px-2 py-1 text-xs font-semibold text-black">
                {event.source_count} fuentes
              </span>
            </div>

            {/* Event title */}
            <h2 className="text-xl font-bold leading-snug">
              {event.title}
            </h2>

            {/* Partisan distribution */}
            <div className="mt-4">
              <PartisanBar
                colorado={event.colorado_pct}
                neutro={event.neutro_pct}
                anticolorado={event.anticolorado_pct}
              />
            </div>

            {/* Classification coverage */}
            {event.unclassified_source_count > 0 && (
              <p className="mt-2 text-xs text-gray-300">
                Clasificación disponible para{" "}
                {event.classified_source_count} de{" "}
                {event.source_count} fuentes
              </p>
            )}

          </div>
        </Link>
      ))}
    </div>
  );
}

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[#FFFFFF]">
      <header className="bg-[#FFFFFF]">
        <div className="mx-auto flex items-center gap-5 px-6 py-5">
          <img
          src="/BI.png"
          alt="Dubito Noticias"
          className="h-25 w-auto object-contain"
        />

        <div className={`flex gap-2 ${libreBaskerville.className}`}>
          <Link href="/" className="text-4xl font-bold">
            DUBITO
            <p style={{ color: "gray", fontSize: "14px" }}>
              Noticias sobre noticias
            </p>
          </Link>

          <nav className="ml-25 flex gap-6 py-5 text-sm">
            <Link href="/">Inicio</Link>
            <Link href="/datos">Datos</Link>
          </nav>
        </div>
      </div>

      {/* Three colored lines below the header */}
      <div className="w-full">
        <div className="h-[2px] bg-[#2e4c8c]" />
        <div className="h-[2px] bg-[#fff3e1]" />
        <div className="h-[2px] bg-[#fa2d1a]" />
      </div>
    </header>

      <section className="mx-auto max-w-7xl px-6 py-10">
        

        

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
