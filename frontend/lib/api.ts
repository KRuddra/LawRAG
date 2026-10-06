/**
 * API client for backend communication
 * Adapted for Wisconsin Law Enforcement Legal Chat RAG System
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface ChatMessage {
  message: string;
  conversation_id?: string;
  jurisdiction?: string;
  categories?: string[];
}

export interface ChatScope {
  jurisdiction?: string;
  categories?: string[];
}

export interface SourceDocument {
  text: string;
  metadata: {
    source_id: string;
    title: string;
    statute_number?: string;
    case_citation?: string;
    source_uri: string;
    chunk_id?: string;
    doc_type?: string;
    jurisdiction?: string;
    [key: string]: any;
  };
  score: number;
}

export interface ChatResponse {
  response: string;
  sources: SourceDocument[];
  confidence: number;
  flags: string[];
  conversation_id: string;
}

/**
 * Send a chat message to the backend
 */
export async function sendChatMessage(
  message: string,
  conversationId?: string,
  scope?: ChatScope
): Promise<ChatResponse> {
  const payload: ChatMessage = {
    message,
    ...(conversationId && { conversation_id: conversationId }),
    ...(scope?.jurisdiction && { jurisdiction: scope.jurisdiction }),
    ...(scope?.categories && scope.categories.length > 0 && { categories: scope.categories }),
  };

  const response = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error: ${response.status} ${response.statusText} - ${errorText}`);
  }

  return await response.json();
}

/**
 * Health check endpoint
 */
export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_URL}/health`);
  
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  
  return await response.json();
}
