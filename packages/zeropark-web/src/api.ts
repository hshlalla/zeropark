export type TaskRequest = {
  prompt: string;
  capability?: string;
  params?: Record<string, any>;
};

export type Artifact = {
  id: string;
  kind: string;
  title: string;
  mime_type: string;
  uri?: string;
  inline?: string;
  metadata?: Record<string, any>;
};

export type SourceRef = {
  url: string;
  provider_id: string;
  metadata?: Record<string, any>;
};

export type TaskResult = {
  task_id: string;
  status: string;
  capability: string;
  provider_id?: string;
  artifacts: Artifact[];
  sources?: SourceRef[];
  metrics?: Record<string, any>;
  error?: string;
};

const API_BASE = "http://localhost:8000";

export async function executeTask(request: TaskRequest): Promise<TaskResult> {
  const response = await fetch(`${API_BASE}/tasks`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`API Error ${response.status}: ${errText}`);
  }

  return response.json();
}
