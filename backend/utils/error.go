package utils

import (
	"errors"
	"net/http"
)

var (
	ErrNotFound = errors.New("resource not found")
	ErrInvalidInput = errors.New("invalid input")
	ErrInternal = errors.New("internal server error")
)

func JSONError(w http.ResponseWriter, status int, message string) {
	JSON(w, status, map[string]string{"error": message})
}

func HTMLError(w http.ResponseWriter, status int, message string) {
	http.Error(w, message, status)
}
