import { IUser } from './types';

export interface IUserRepository {
  findById(id: number): IUser | null;
  findAll(): IUser[];
}

export class UserApi implements IUserRepository {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  findById(id: number): IUser | null {
    return null;
  }

  findAll(): IUser[] {
    return [];
  }
}

export type ApiResponse<T> = {
  data: T;
  status: number;
  message: string;
};
