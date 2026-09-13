import { useEffect, useState } from 'react';
import { workspaceService } from '../services/workspaceService';

export function usePersistentState<T>(name: string, initial: T) {
  const [value, setValue] = useState<T>(() => workspaceService.getRaw(name, initial));
  useEffect(() => { workspaceService.set(name, value); }, [name, value]);
  return [value, setValue] as const;
}
