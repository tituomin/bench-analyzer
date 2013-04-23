
BEGIN {
    OFS=","
    split(fields, f, " ")
    for (fieldname in f) {
        printf "%s,", f[fieldname]
    }
    print ""
}

/^[^0-9]+$/ {
    for(i=0;i<NF;i++){
        column_no[$i] = i;
    }
    next
}

1 {
    for(fieldname in f) {
        col=column_no[f[fieldname]]
        if ($col=="" || $col=="-") {
            printf "%s", "X,"
        }
        else {
            printf "%s,", $col
        }
    }
    print ""
}
