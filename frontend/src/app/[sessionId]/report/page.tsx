"use client";
import { use } from "react";
import ExportReport from "@/components/export-report";
import { useSession } from "../SessionProvider";
import { useRouter } from "next/navigation";

export default function ExportReportPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const { cachedInsights, setCachedInsights, recommendedMethod, cleaningRationale } = useSession();
  const router = useRouter();
  
  return (
    <div className="w-full mt-10">
      <ExportReport sessionId={sessionId}  />
    </div>
  );
}