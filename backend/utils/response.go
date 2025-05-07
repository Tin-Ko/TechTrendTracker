package utils

import (
	"encoding/json"
	"net/http"
	"fmt"
)


func JSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)

	fmt.Println(data)

	json.NewEncoder(w).Encode(data)
}
