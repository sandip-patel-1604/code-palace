import { IUser, UserId } from './types';
import { UserApi } from './api';

export class UserController {
  private api: UserApi;

  constructor(api: UserApi) {
    this.api = api;
  }

  getUser(id: UserId): IUser | null {
    return null;
  }

  listUsers(): IUser[] {
    return [];
  }
}

export function bootstrapApp(port: number): void {
  console.log(`Starting on port ${port}`);
}

export const formatUser = (user: IUser): string => {
  return `${user.id}: ${user.name}`;
};
