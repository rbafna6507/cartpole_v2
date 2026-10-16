static void parameter_core_guards(){
 Core c=ready();assert(send(c,"V2 PARAM 7 pw").kind!=ERROR);
 assert(send(c,"V2 PARAM 7 pw 6").kind!=ERROR);
 check_error(c,"V2 PARAM 8 pw");check_error(c,"V2 PARAM 7");
 check_error(c,"V2 PARAM 7 pw 6 extra");check_error(c,"V2 PARAM 7 pw nan");
 check_error(c,"V2 PARAM 7 pw inf");check_error(c,"V2 PARAM 7 pw 1e100");
 check_error(c,"V2 PARAM 7 bad-name 6");
 arm(c);check_error(c,"V2 PARAM 7 pw");check_error(c,"V2 PARAM 7 pw 6");
 c.trip(ENCODER);assert(send(c,"V2 PARAM 7 pw").kind!=ERROR);
 check_error(c,"V2 PARAM 7 pw 6");send(c,"V2 CLEAR 7");
 c.sample(false,0);assert(send(c,"V2 PARAM 7 pw").kind!=ERROR);
 check_error(c,"V2 PARAM 7 pw 6");c.sample(true,0);
 assert(send(c,"V2 CALIBRATE 7 upright").kind==OK);
 check_error(c,"V2 PARAM 7 pw");check_error(c,"V2 PARAM 7 pw 6");
}
