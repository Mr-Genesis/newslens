import DeepDiveView from "@/components/DeepDiveView";

export const dynamic = "force-static";
export const dynamicParams = false;

export async function generateStaticParams() {
  return [];
}

export default async function DeepDivePage() {
  return <DeepDiveView />;
}
