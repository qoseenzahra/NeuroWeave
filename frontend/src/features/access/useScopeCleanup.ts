import { useEffect, useRef } from "react";
import { clearScopeStorage } from "./authorization";
import { clearAllPendingTurnScopes } from "../chat/chatTurns";

export function useScopeCleanup(
  userId: string | undefined,
  projectId: string | undefined,
): void {
  const previous = useRef<string | undefined>(undefined);

  useEffect(() => {
    const current = [userId ?? "", projectId ?? ""].join(":");
    if (previous.current !== undefined && previous.current !== current) {
      clearAllPendingTurnScopes();
      if (previous.current) {
        const [oldUser, oldProject] = previous.current.split(":");
        clearScopeStorage(oldUser, oldProject || undefined);
      }
    }
    previous.current = current;
  }, [userId, projectId]);
}
