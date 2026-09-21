import { useQuery } from '@tanstack/react-query';
import { fetchSkills } from './skillsApi';

export function useSkills() {
  return useQuery({
    queryKey: ['skills'],
    queryFn: ({ signal }) => fetchSkills(signal),
    staleTime: 30_000,
    retry: 1
  });
}
