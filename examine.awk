
BEGIN {
    OFS=","
    split(fieldnames, f, " ")
}

NR == 1 {
    for(i=0;i<NF;i++){
        column_no[$i] = i;
    }
    for(fieldname in f) {
        printf "%s,", f[fieldname]
    }
    print ""
}

NR > 1 {
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
