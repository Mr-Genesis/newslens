import DeepDiveView from "@/components/DeepDiveView";

// For static export (Capacitor), Capacitor uses /story?id=X instead.
export function generateStaticParams(): { clusterId: string }[] {
  return [];
}

export default async function DeepDivePage({
  params,
}: {
  params: Promise<{ clusterId: string }>;
}) {
  return <DeepDiveView />;
}
