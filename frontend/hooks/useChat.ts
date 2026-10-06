'use client';

import { useState, useCallback } from 'react';
import { sendChatMessage, ChatScope } from '../lib/api';
import { Message } from '../lib/types';

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>();

  const sendMessage = useCallback(async (messageText: string, scope?: ChatScope) => {
    if (!messageText.trim()) return;

    // Add user message immediately
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: messageText,
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setLoading(true);
    setError(null);

    try {
      // Call backend API
      const response = await sendChatMessage(messageText, conversationId, scope);

      // Add AI response
      const aiMessage: Message = {
        id: `ai-${Date.now()}`,
        role: 'ai',
        content: response.response,
        sources: response.sources,
        confidence: response.confidence,
        flags: response.flags,
        timestamp: new Date().toISOString(),
      };

      setMessages(prev => [...prev, aiMessage]);

      // Update conversation ID if provided
      if (response.conversation_id && !conversationId) {
        setConversationId(response.conversation_id);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to send message');
      console.error('Error sending message:', err);
      
      // Add error message to chat
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'ai',
        content: 'Sorry, I encountered an error. Please try again.',
        error: true,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
    setConversationId(undefined);
  }, []);

  return {
    messages,
    loading,
    error,
    conversationId,
    sendMessage,
    clearMessages,
  };
}

