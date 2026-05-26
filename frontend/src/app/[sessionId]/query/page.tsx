"use client";
import { use } from "react";
import Query from "@/components/query";
import { useSession } from "../SessionProvider";
import { useRouter } from "next/navigation";

export default function QueryPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const router = useRouter();
  
  return (
    <div className="w-full mt-10">
      <Query sessionId={sessionId} />
      <div className="mt-8 flex justify-end"><button onClick={() => router.push(`/${sessionId}/report`)} className="px-6 py-3 bg-white text-black font-medium rounded-xl hover:bg-neutral-200 transition-colors">Report &rarr;</button></div>
    </div>
  );
}