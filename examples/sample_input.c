int counter = 1;

int add_one(int v) {
    int next = v + 1;
    return next;
}

int tick(void) {
    if (counter < 10) {
        counter = add_one(counter);
    }
    return counter;
}
