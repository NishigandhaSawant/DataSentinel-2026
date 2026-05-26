"use client";
import { use } from "react";
import Insights from "@/components/insights";
import { useSession } from "../SessionProvider";
import { useRouter } from "next/navigation";

export default function InsightsPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const { cachedInsights, setCachedInsights } = useSession();
  const router = useRouter();
  
  return (
    <div className="w-full mt-10">
      <Insights sessionId={sessionId} cachedInsights={cachedInsights} onInsightsLoaded={setCachedInsights} />
      <div className="mt-8 flex justify-end"><button onClick={() => router.push(`/${sessionId}/clean`)} className="px-6 py-3 bg-white text-black font-medium rounded-xl hover:bg-neutral-200 transition-colors">Next &rarr;</button></div>
    </div>
  );
}