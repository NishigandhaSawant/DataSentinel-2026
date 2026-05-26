"use client";
import { use } from "react";
import Clean from "@/components/clean";
import { useSession } from "../SessionProvider";
import { useRouter } from "next/navigation";

export default function CleanPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const { cachedInsights, setCachedInsights, recommendedMethod, cleaningRationale } = useSession();
  const router = useRouter();
  
  return (
    <div className="w-full mt-10">
      <Clean sessionId={sessionId} recommendedMethod={recommendedMethod} cleaningRationale={cleaningRationale} onComplete={() => router.push(`/${sessionId}/compare`)} />
    </div>
  );
}