"use client";
import { use } from "react";
import Detection from "@/components/detection";
import { useSession } from "../SessionProvider";
import { useRouter } from "next/navigation";

export default function DetectionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const router = useRouter();
  
  return (
    <div className="w-full mt-10">
      <div className="mb-6"><h2 className="text-2xl font-semibold mb-1">Anomaly Detection Engine</h2><p className="text-neutral-400">Review flagged shards.</p></div>
      <Detection sessionId={sessionId} />
      <div className="mt-8 flex justify-end"><button onClick={() => router.push(`/${sessionId}/insights`)} className="px-6 py-3 bg-white text-black font-medium rounded-xl shadow-lg hover:bg-neutral-200 transition-colors">Proceed &rarr;</button></div>
    </div>
  );
}