"use client";
import { use } from "react";
import ReviewEdit from "@/components/review-edit";
import { useSession } from "../SessionProvider";
import { useRouter } from "next/navigation";

export default function ReviewEditPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const { cachedInsights, setCachedInsights, recommendedMethod, cleaningRationale } = useSession();
  const router = useRouter();
  
  return (
    <div className="w-full mt-10">
      <ReviewEdit sessionId={sessionId}  />
    </div>
  );
}