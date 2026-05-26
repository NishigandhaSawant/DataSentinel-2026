"use client";
import { use } from "react";
import Visualizer from "@/components/visualizer";
import { useSession } from "../SessionProvider";
import { useRouter } from "next/navigation";

export default function VisualizerPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const { cachedInsights, setCachedInsights, recommendedMethod, cleaningRationale } = useSession();
  const router = useRouter();
  
  return (
    <div className="w-full mt-10">
      <Visualizer sessionId={sessionId}  />
    </div>
  );
}