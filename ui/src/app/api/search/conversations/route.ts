import { NextRequest, NextResponse } from "next/server";
import { searchConversations } from "@/lib/typesense";
import type { ConversationFilters, PaginationOptions } from "@/lib/types";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const query: string = body.query ?? "*";
    const filters: ConversationFilters = body.filters ?? {};
    const pagination: PaginationOptions = body.pagination ?? {};

    const results = await searchConversations(query, filters, pagination);
    return NextResponse.json(results);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Search failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
