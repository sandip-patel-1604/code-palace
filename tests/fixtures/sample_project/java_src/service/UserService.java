package com.example.service;

import java.util.List;
import java.util.Optional;

public class UserService {
    private String name;
    public static final int MAX_USERS = 1000;

    public UserService(String name) {
        this.name = name;
    }

    public String getName() {
        return this.name;
    }

    public List<String> listUsers() {
        return new java.util.ArrayList<>();
    }

    private boolean validate(String input) {
        return input != null && !input.isEmpty();
    }
}

public interface IUserRepository {
    List<String> findAll();
}
